"""
Scraper Lidl.fr
===============
Lidl expose un sitemap gzippe avec ~10 000 produits.
Chaque page produit contient du JSON-LD structure.

Strategie :
  1. Telecharger le sitemap gzippe depuis lidl.fr/static/sitemap.xml
  2. Filtrer les URLs produits alimentaires
  3. Pour chaque URL, extraire le JSON-LD (nom, prix, marque, image)

Usage :
  python scraper_lidl.py --max-products 20
  python scraper_lidl.py --category "fromage"
"""

import argparse
import gzip
import json
import os
import re
import xml.etree.ElementTree as ET

import cloudscraper
from bs4 import BeautifulSoup

from config import OUTPUT_DIR, REQUEST_TIMEOUT, get_logger, rate_limit
from models import Product, save_products

log = get_logger("lidl")

SITEMAP_INDEX = "https://www.lidl.fr/static/sitemap.xml"

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

scraper = cloudscraper.create_scraper()


def fetch_sitemap_urls() -> list[str]:
    """Fetch all product URLs from Lidl sitemap (gzipped)."""
    log.info(f"Fetching sitemap index: {SITEMAP_INDEX}")

    resp = scraper.get(SITEMAP_INDEX, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    all_urls = []
    for sm in root.findall("sm:sitemap", NS):
        loc = sm.find("sm:loc", NS)
        if loc is None:
            continue
        url = loc.text
        if "product" not in url.lower():
            continue

        log.info(f"Fetching product sitemap: {url}")
        rate_limit()
        resp = scraper.get(url, timeout=60)
        resp.raise_for_status()

        content = resp.content
        if url.endswith(".gz"):
            content = gzip.decompress(content)

        sub_root = ET.fromstring(content)
        for url_el in sub_root.findall("sm:url", NS):
            loc2 = url_el.find("sm:loc", NS)
            if loc2 is not None and "/p/" in loc2.text:
                all_urls.append(loc2.text)

    log.info(f"Found {len(all_urls)} product URLs")
    return all_urls


def scrape_product_page(url: str) -> Product | None:
    """Scrape a single Lidl product page using JSON-LD."""
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
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]

        for item in items:
            if item.get("@type") != "Product":
                continue

            offers = item.get("offers", [])
            if isinstance(offers, list):
                offers = offers[0] if offers else {}

            price = 0.0
            try:
                price = float(offers.get("price", 0))
            except (ValueError, TypeError):
                pass

            brand_data = item.get("brand", {})
            brand = ""
            if isinstance(brand_data, dict):
                brand = brand_data.get("name", "")
            elif isinstance(brand_data, str):
                brand = brand_data

            images = item.get("image", [])
            image_url = ""
            if isinstance(images, list) and images:
                image_url = images[0]
            elif isinstance(images, str):
                image_url = images

            return Product(
                name=item.get("name", ""),
                price=price,
                currency=offers.get("priceCurrency", "EUR"),
                brand=brand,
                image_url=image_url,
                product_url=url,
                sku=str(item.get("sku", "")),
                enseigne="Lidl",
                category=extract_category_from_url(url),
            )

    return None


def extract_category_from_url(url: str) -> str:
    """Extract product slug from Lidl URL: /p/{slug}/p{id}"""
    match = re.search(r"/p/([^/]+)/p\d+", url)
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
    save_products(products, os.path.join(OUTPUT_DIR, "lidl_products.json"))
    return products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Lidl.fr")
    parser.add_argument("--max-products", type=int, default=0, help="Max products (0=all)")
    parser.add_argument("--category", type=str, default="", help="Filter by keyword in URL")
    args = parser.parse_args()

    run(max_products=args.max_products, category_filter=args.category)
