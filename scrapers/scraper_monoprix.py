"""
Scraper Monoprix - Courses alimentaires
========================================
Les produits alimentaires sont sur courses.monoprix.fr (pas monoprix.fr).
Chaque page produit expose un JSON-LD structure avec nom, prix, marque, taille.

Strategie :
  1. Parser le sitemap courses.monoprix.fr/sitemaps/sitemap-products-part1.xml
  2. Filtrer les URLs par categorie alimentaire
  3. Pour chaque URL, extraire le JSON-LD

Usage :
  python scraper_monoprix.py --max-products 20
  python scraper_monoprix.py --category "lait"
  python scraper_monoprix.py --category "cafe"
"""

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET

import cloudscraper
from bs4 import BeautifulSoup

from config import OUTPUT_DIR, REQUEST_TIMEOUT, get_logger, rate_limit
from models import Product, save_products

log = get_logger("monoprix")

SITEMAP_INDEX = "https://courses.monoprix.fr/sitemaps/sitemap_index.xml"

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

scraper = cloudscraper.create_scraper()


def fetch_sitemap_urls() -> list[str]:
    """Fetch all product URLs from the courses.monoprix.fr sitemap."""
    log.info(f"Fetching sitemap index: {SITEMAP_INDEX}")

    resp = scraper.get(SITEMAP_INDEX, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    all_urls = []
    for sitemap in root.findall("sm:sitemap", NS):
        loc = sitemap.find("sm:loc", NS)
        if loc is not None and "product" in loc.text:
            log.info(f"Fetching product sitemap: {loc.text}")
            rate_limit()
            resp = scraper.get(loc.text, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            sub_root = ET.fromstring(resp.content)
            for url_el in sub_root.findall("sm:url", NS):
                loc2 = url_el.find("sm:loc", NS)
                if loc2 is not None:
                    all_urls.append(loc2.text)

    log.info(f"Found {len(all_urls)} product URLs")
    return all_urls


def scrape_product_page(url: str) -> Product | None:
    """Scrape a single product page using JSON-LD."""
    try:
        resp = scraper.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            log.debug(f"HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        log.debug(f"Request failed for {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    return extract_json_ld(soup, url)


def extract_json_ld(soup: BeautifulSoup, url: str) -> Product | None:
    """Extract product data from JSON-LD script tags."""
    script = soup.find("script", type="application/ld+json")
    if not script or not script.string:
        return None

    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        return None

    if data.get("@type") != "Product":
        return None

    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = 0.0
    try:
        price = float(offers.get("price", 0))
    except (ValueError, TypeError):
        pass

    brand = data.get("brand", "")
    if isinstance(brand, dict):
        brand = brand.get("name", "")

    images = data.get("image", [])
    image_url = ""
    if isinstance(images, list) and images:
        image_url = images[0]
    elif isinstance(images, str):
        image_url = images

    size = data.get("size", "")

    return Product(
        name=data.get("name", ""),
        price=price,
        currency=offers.get("priceCurrency", "EUR"),
        unit_price=size,
        brand=brand,
        image_url=image_url,
        product_url=url,
        sku=data.get("sku", ""),
        enseigne="Monoprix",
        category=extract_category_from_url(url),
    )


def extract_category_from_url(url: str) -> str:
    """Extract product slug from URL."""
    match = re.search(r"/products/([^/]+)/", url)
    if match:
        return match.group(1)
    return ""


def run(max_products: int = 0, category_filter: str = ""):
    """Main scraping loop."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    urls = fetch_sitemap_urls()
    if not urls:
        log.error("No product URLs found. Exiting.")
        return []

    if category_filter:
        urls = [u for u in urls if category_filter.lower() in u.lower()]
        log.info(f"Filtered to {len(urls)} URLs matching '{category_filter}'")

    if max_products > 0:
        urls = urls[:max_products]
        log.info(f"Limited to {max_products} products")

    products = []
    for i, url in enumerate(urls):
        log.info(f"[{i+1}/{len(urls)}] {url}")
        product = scrape_product_page(url)
        if product:
            products.append(product)
            log.info(f"  -> {product.name} | {product.price} EUR | {product.brand}")
        else:
            log.warning(f"  -> No data extracted")
        rate_limit()

    log.info(f"Total products scraped: {len(products)}")
    save_products(products, os.path.join(OUTPUT_DIR, "monoprix_products.json"))
    return products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Monoprix courses alimentaires")
    parser.add_argument("--max-products", type=int, default=0, help="Max products (0=all)")
    parser.add_argument("--category", type=str, default="", help="Filter by keyword in URL")
    args = parser.parse_args()

    run(max_products=args.max_products, category_filter=args.category)
