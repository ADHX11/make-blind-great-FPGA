"""Compile/elaborate the RTL and testbench with pyslang; does NOT simulate.

Install: python -m pip install pyslang==11.0.0
Run from any directory: python fpga/sim/check_syntax.py
"""
from pathlib import Path
import sys


def main() -> int:
    try:
        import pyslang
        from pyslang.ast import Compilation
        from pyslang.syntax import SyntaxTree
    except ImportError:
        print("NOT RUN: install pyslang==11.0.0 for syntax/elaboration checking.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    compilation = Compilation()
    sources = [root / line.strip() for line in (root / "rtl/files.f").read_text().splitlines()
               if line.strip() and not line.lstrip().startswith("#")]
    sources.append(root / "sim/tb_blind_printer_core.sv")
    for source in sources:
        compilation.addSyntaxTree(SyntaxTree.fromFile(str(source)))
    diagnostics = compilation.getAllDiagnostics()
    if diagnostics:
        print(pyslang.DiagnosticEngine.reportAll(compilation.sourceManager, diagnostics))
    if any(diagnostic.isError() for diagnostic in diagnostics):
        print("FAIL: syntax/elaboration errors; behavioral simulation was not run.", file=sys.stderr)
        return 1
    print(f"PASS: syntax/elaboration only ({len(diagnostics)} diagnostics); behavioral simulation was not run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
