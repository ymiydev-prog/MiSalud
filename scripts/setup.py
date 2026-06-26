#!/usr/bin/env python3
"""MiSalud — All-in-one setup script.
Creates the virtualenv, installs deps, and initializes the database.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def run(cmd: str, **kwargs):
    print(f"  → {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=PROJECT_ROOT, **kwargs)


def main():
    print("=== MiSalud Setup ===\n")

    # 1. Create virtualenv if missing
    venv_dir = PROJECT_ROOT / ".venv"
    if not venv_dir.exists():
        print("[1/3] Creating virtualenv...")
        run(f"{sys.executable} -m venv .venv")
    else:
        print("[1/3] Virtualenv already exists")

    # 2. Install dependencies
    print("[2/3] Installing dependencies...")
    pip = str(venv_dir / "bin" / "pip")
    run(f"{pip} install -r requirements.txt --quiet")

    # 3. Initialize database
    print("[3/3] Initializing database...")
    python = str(venv_dir / "bin" / "python")
    run(f"{python} -c 'from src.database import init_db; init_db(); print(\"  DB ready\")'")

    print("\n=== Setup Complete ===")
    print(f"Activate: source {venv_dir}/bin/activate")
    print(f"Dashboard: streamlit run src/dashboard.py")


if __name__ == "__main__":
    main()
