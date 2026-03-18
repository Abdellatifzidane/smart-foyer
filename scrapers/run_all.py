"""
Run All Scrapers
================
Orchestrates the scraping of all supported retailers
and merges results into a single unified dataset.

Usage :
  python run_all.py
  python run_all.py --retailers carrefour,monoprix
  python run_all.py --max-products 50
"""

import argparse
import json
import os
from datetime import datetime, timezone

from config import OUTPUT_DIR, get_logger
from models import Product

log = get_logger("runner")


def run_monoprix(max_products: int) -> list[Product]:
    from scraper_monoprix import run
    return run(max_products=max_products)


def run_lidl(max_products: int) -> list[Product]:
    from scraper_lidl import run
    return run(max_products=max_products)


RETAILERS = {
    "monoprix": run_monoprix,
    "lidl": run_lidl,
}


def merge_results(all_products: list[Product]):
    """Merge all products into a single JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, f"all_products_{timestamp}.json")

    data = [p.to_dict() for p in all_products]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"Merged {len(data)} products into {filepath}")

    # Print summary
    by_enseigne = {}
    for p in all_products:
        by_enseigne.setdefault(p.enseigne, 0)
        by_enseigne[p.enseigne] += 1

    log.info("Summary:")
    for enseigne, count in sorted(by_enseigne.items()):
        log.info(f"  {enseigne}: {count} products")


def main():
    parser = argparse.ArgumentParser(description="Run SmartFoyer scrapers")
    parser.add_argument("--retailers", type=str, default="",
                        help="Comma-separated list (default: all)")
    parser.add_argument("--max-products", type=int, default=0,
                        help="Max products per retailer (0=all)")
    args = parser.parse_args()

    selected = args.retailers.split(",") if args.retailers else list(RETAILERS.keys())

    all_products = []
    for name in selected:
        name = name.strip().lower()
        if name not in RETAILERS:
            log.warning(f"Unknown retailer: {name}. Available: {list(RETAILERS.keys())}")
            continue

        log.info(f"{'='*60}")
        log.info(f"Starting scraper: {name.upper()}")
        log.info(f"{'='*60}")

        try:
            products = RETAILERS[name](args.max_products)
            all_products.extend(products)
            log.info(f"{name}: scraped {len(products)} products")
        except Exception as e:
            log.error(f"{name}: scraper failed: {e}")

    if all_products:
        merge_results(all_products)
    else:
        log.warning("No products scraped.")


if __name__ == "__main__":
    main()
