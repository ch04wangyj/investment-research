#!/usr/bin/env python
"""Initialize or rebuild the local SQLite database.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --reset
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    import yaml

    from config.settings import get_settings
    from src.storage.repository import (
        AgentReportRepository,
        MarketDataRepository,
        TrackedSymbolRepository,
    )

    parser = argparse.ArgumentParser(description="Initialize local research database")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all local tables")
    args = parser.parse_args()

    settings = get_settings()
    db_path = settings.operational_db_path
    repo_classes = [MarketDataRepository, AgentReportRepository, TrackedSymbolRepository]

    if args.reset:
        print("Dropping existing local tables...")
        MarketDataRepository(db_path).drop_tables()

    for repo_cls in repo_classes:
        repo = repo_cls(db_path)
        repo.create_tables()
        print(f"Created tables via {repo_cls.__name__}")

    config_path = PROJECT_ROOT / "config" / "markets.yaml"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            markets = yaml.safe_load(f) or {}
        repo = TrackedSymbolRepository(db_path)
        for market_key in ["ashare", "us", "hk"]:
            market = markets.get(market_key, {})
            exchange = market.get("data_source", market_key)
            for stock in market.get("tracked_stocks", []):
                repo.add(
                    symbol=stock["symbol"].upper(),
                    name=stock["name"],
                    exchange=market_key,
                    sector=stock.get("sector", ""),
                )
                print(f"  Seeded {stock['symbol']} ({stock['name']}) - {exchange}")

    print(f"\nDatabase initialized at: {db_path}")


if __name__ == "__main__":
    main()
