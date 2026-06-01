#!/usr/bin/env python
"""Refresh the auditable public-research intelligence library."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.intelligence import refresh_research_intelligence


def main() -> None:
    overview = refresh_research_intelligence()
    print(json.dumps(overview["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
