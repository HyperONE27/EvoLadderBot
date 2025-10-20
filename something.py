#!/usr/bin/env python3
import subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"

def run(title, cmd):
    print(f"\n=== {title} ===")
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print(f"✅ {title} passed")
        return True
    print(f"❌ {title} failed")
    return False

def main():
    os.chdir(ROOT)
    steps = [
        ("Format with black", f"python -m black {SRC_DIR}"),
        ("Lint with flake8", f"python -m flake8 {SRC_DIR} --count --statistics"),
        ("Compile syntax", f"python -m compileall -q ."),
    ]

    all_ok = True
    for title, cmd in steps:
        all_ok &= run(title, cmd)

    print("\n=== Summary ===")
    if all_ok:
        print("🎉 All checks passed!")
        sys.exit(0)
    else:
        print("⚠️ Some checks failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
