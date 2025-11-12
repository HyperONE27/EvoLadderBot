#!/usr/bin/env python3
"""
Lightweight project setup script.
Creates a venv, installs requirements, and copies the example .env if missing.
"""

import os, sys, subprocess, shutil

venv = ".venv"
if not os.path.exists(venv):
    print("🪄 Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", venv])

activate = os.path.join(venv, "Scripts" if os.name == "nt" else "bin", "activate")
print(f"✅ Virtual environment ready ({activate})")

print("📦 Installing dependencies...")
subprocess.check_call([os.path.join(venv, "Scripts" if os.name == "nt" else "bin", "pip"), "install", "-r", "requirements.txt"])

if not os.path.exists(".env"):
    if os.path.exists(".env.example"):
        shutil.copy(".env.example", ".env")
        print("✨ Created .env from .env.example")
    else:
        print("⚠️ No .env.example found, skipping.")

print("✅ Setup complete! Run:")
print(f"    {activate}")
print("Then:")
print("    python -m src.bot.main")
