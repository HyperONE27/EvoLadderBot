"""Convenience entry point for running the full test suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_PYTEST_ARGS = ["-m", "not slow", "-q"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run project tests", add_help=False)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    known_args, unknown_args = parser.parse_known_args()
    if unknown_args:
        known_args.pytest_args = unknown_args + known_args.pytest_args
    return known_args


def main() -> int:
    args = parse_args()
    pytest_args = args.pytest_args or DEFAULT_PYTEST_ARGS

    tests_root = Path(__file__).resolve().parent
    project_root = tests_root.parent
    result = subprocess.run([sys.executable, "-m", "pytest", *pytest_args], cwd=project_root)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
