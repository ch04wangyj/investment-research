#!/usr/bin/env python
"""First-run setup: install dependencies, create .env, init database.

Usage:
    cd investment-research
    python scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    print("=" * 60)
    print("  AI Investment Research — Phase 1 Setup")
    print("=" * 60)

    # Step 1: .env file
    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        print("\n[1/3] Creating .env from .env.example...")
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Created {env_file}")
        print("  IMPORTANT: Edit .env and add your DEEPSEEK_API_KEY before running analysis!")
    elif env_file.exists():
        print("\n[1/3] .env already exists — skipping")
    else:
        print("\n[1/3] No .env.example found — create .env manually with DEEPSEEK_API_KEY")

    # Step 2: Install dependencies
    print("\n[2/3] Installing dependencies...")
    req_file = PROJECT_ROOT / "pyproject.toml"
    if req_file.exists():
        # Use pip to install from pyproject.toml
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Dependencies installed successfully!")
            # Also install key extras
            for extra in ["duckduckgo-search"]:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", extra],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                )
            print("  Web search dependency installed!")
        else:
            print(f"  Warning: pip install had issues:\n{result.stderr[-500:]}")
            print("  You may need to install dependencies manually.")

    # Step 3: Initialize database
    print("\n[3/3] Initializing database...")
    subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "init_db.py")])

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print(f"""
Next steps:
  1. Edit .env and add your DEEPSEEK_API_KEY
  2. Test analysis:  python scripts/run_analysis.py 600519
  3. Launch dashboard: python scripts/run_dashboard.py
""")


if __name__ == "__main__":
    main()
