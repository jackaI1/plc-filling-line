"""Pinned OpenPLC v3 compiler bootstrap and native PLC library build."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REV = "75d6e82cce5bc8b98ce03a417b106884cbb7ebb5"


def run(args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def build(matiec=None):
    target = ROOT / ".build"
    target.mkdir(exist_ok=True)
    compiler = Path(matiec).resolve() if matiec else target / "matiec"
    if not (compiler / "iec2c").exists():
        if matiec:
            raise RuntimeError("Build the supplied matiec directory first")
        if not (compiler / ".git").exists():
            run(["git", "init", compiler])
            run(["git", "remote", "add", "origin", "https://github.com/thiagoralves/matiec.git"], compiler)
        run(["git", "fetch", "--depth", "1", "origin", REV], compiler)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], compiler)
        run(["autoreconf", "-i"], compiler)
        run(["./configure"], compiler)
        run(["make", "-j2"], compiler)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=compiler, text=True).strip()
    if actual != REV:
        raise RuntimeError(f"Expected pinned matiec {REV}, got {actual}")
    run([sys.executable, ROOT / "tools/openplc_export.py", "--check"])
    generated = target / "generated"
    generated.mkdir(exist_ok=True)
    run([compiler / "iec2c", "-I", compiler / "lib", "-T", generated, ROOT / "plc/line.st"])
    library = target / ("line.dylib" if platform.system() == "Darwin" else "line.so")
    run([os.environ.get("CC", "cc"), "-dynamiclib" if platform.system() == "Darwin" else "-shared",
         "-fPIC", "-std=c99", "-Wno-unused-function", "-Wno-varargs", "-I", compiler / "lib/C", "-I", generated,
         ROOT / "plc/bridge.c", "-o", library])
    print(f"Built {library.relative_to(ROOT)} from PLCopen ladder XML")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--matiec", help="Existing pinned compiler checkout")
    build(parser.parse_args().matiec)
