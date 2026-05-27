#!/usr/bin/env python
"""Launch the Streamlit dashboard from the project root.

Usage:
    cd investment-research
    python scripts/run_dashboard.py
    # Or: streamlit run src/dashboard/app.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    app_path = PROJECT_ROOT / "src" / "dashboard" / "app.py"
    if not app_path.exists():
        print(f"ERROR: Dashboard not found at {app_path}")
        sys.exit(1)

    print(f"Starting Streamlit dashboard from: {PROJECT_ROOT}")
    print(f"Dashboard URL: http://localhost:8501")
    print("Press Ctrl+C to stop.\n")

    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        cwd=str(PROJECT_ROOT),
    )


if __name__ == "__main__":
    main()
