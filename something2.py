#!/usr/bin/env python3
"""
cleanup_code_quality.py

1. Auto-fixes simple issues using Ruff.
2. Runs Flake8 for serious problems (F821, F811, F541).
3. Prints colored results.

Usage:
    python cleanup_code_quality.py
"""

import subprocess
import sys
import shutil

# Colors for output (works in PowerShell, CMD, Cursor, etc.)
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def run_step(title: str, cmd: str) -> int:
    """Run a command and print section headers."""
    print(f"\n{YELLOW}=== {title} ==={RESET}")
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        print(f"{GREEN}✅ {title} passed{RESET}")
    else:
        print(f"{RED}❌ {title} found issues (exit {result.returncode}){RESET}")
    return result.returncode


def main() -> None:
    # Verify tools exist
    for tool in ["ruff", "flake8"]:
        if not shutil.which(tool):
            print(f"{RED}Error:{RESET} '{tool}' not found. Install with:")
            print(f"    py -m pip install {tool}")
            sys.exit(1)

    # Step 1. Auto-fix easy stuff
    run_step("Ruff Auto-fix (unused imports & vars)", "ruff check src --select F401,F841 --fix")

    # Step 2. Run Flake8 for serious issues only
    print(f"\n{YELLOW}=== Running Flake8 for serious errors (F821,F811,F541) ==={RESET}")
    flake_exit = subprocess.call("flake8 src --select=F821,F811,F541 --statistics", shell=True)

    # Step 3. Summary
    print("\n" + "=" * 60)
    if flake_exit == 0:
        print(f"{GREEN}🎉 Codebase is clean. No serious issues found!{RESET}")
    else:
        print(f"{RED}⚠️  Serious issues remain. Check Flake8 output above.{RESET}")
    print("=" * 60 + "\n")

    sys.exit(flake_exit)


if __name__ == "__main__":
    main()