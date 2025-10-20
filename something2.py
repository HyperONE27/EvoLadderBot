import subprocess
import sys

commands = [
    ("black", "python -m black src"),
    ("flake8", "python -m flake8 src --count --statistics"),
    ("compileall", "python -m compileall -q .")
]

for name, cmd in commands:
    print(f"\n=== Running {name} ===")
    code = subprocess.call(cmd, shell=True)
    if code != 0:
        print(f"❌ {name} failed (exit {code})")
    else:
        print(f"✅ {name} passed")

print("\nDone.")
