"""Configuration for SmartFoyer scrapers."""

import logging
import time

# ─── Rate Limiting ───────────────────────────────────────────────
CRAWL_DELAY = 3  # seconds between requests (ethical scraping)
REQUEST_TIMEOUT = 30  # seconds

# ─── User Agent ──────────────────────────────────────────────────
USER_AGENT = "SmartFoyer-Bot/1.0 (+https://github.com/Abdellatifzidane/smart-foyer; contact@smartfoyer.fr)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)

# ─── Output ──────────────────────────────────────────────────────
OUTPUT_DIR = "data"
LOG_LEVEL = logging.INFO

# ─── Sitemaps ────────────────────────────────────────────────────
SITEMAPS = {
    "monoprix": "https://www.monoprix.fr/sitemap_index.xml",
    "lidl": "https://www.lidl.fr/static/sitemap.xml",
    "picard": "https://www.picard.fr/sitemap_0.xml",
}

# ─── Helpers ─────────────────────────────────────────────────────

def rate_limit():
    """Sleep to respect crawl delay."""
    time.sleep(CRAWL_DELAY)


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    return logging.getLogger(name)
