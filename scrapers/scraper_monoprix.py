"""
Scraper Monoprix.fr
===================
Monoprix utilise Demandware (Salesforce Commerce Cloud) et expose
des donnees JSON-LD structurees sur chaque page produit.

Strategie :
  1. Parser le sitemap_index.xml pour trouver sitemap_0-product.xml
  2. Extraire toutes les URLs produits du sitemap
  3. Pour chaque URL, fetcher la page et extraire le JSON-LD
  4. Le JSON-LD contient : name, sku, brand, price, images, availability

Usage :
  python scraper_monoprix.py
  python scraper_monoprix.py --max-products 100
  python scraper_monoprix.py --category "epicerie"
"""

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from config import (
    CRAWL_DELAY,
    OUTPUT_DIR,
    USER_AGENT,
    REQUEST_TIMEOUT,
    get_logger,
    rate_limit,
)
from models import Product, save_products

log = get_logger("monoprix")

BASE_URL = "https://www.monoprix.fr"
SITEMAP_INDEX = "https://www.monoprix.fr/sitemap_index.xml"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# XML namespaces used in sitemaps
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap_urls() -> list[str]:
    """Fetch all product URLs from the Monoprix sitemap."""
    log.info(f"Fetching sitemap index: {SITEMAP_INDEX}")

    # Step 1: Get sub-sitemaps from index
    resp = requests.get(SITEMAP_INDEX, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    product_sitemap_url = None
    for sitemap in root.findall("sm:sitemap", NS):
        loc = sitemap.find("sm:loc", NS)
        if loc is not None and "product" in loc.text:
            product_sitemap_url = loc.text
            break

    if not product_sitemap_url:
        log.error("No product sitemap found in index")
        return []

    log.info(f"Fetching product sitemap: {product_sitemap_url}")
    rate_limit()

    # Step 2: Get all product URLs
    resp = requests.get(product_sitemap_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    urls = []
    for url_el in root.findall("sm:url", NS):
        loc = url_el.find("sm:loc", NS)
        if loc is not None and "/p/" in loc.text:
            urls.append(loc.text)

    log.info(f"Found {len(urls)} product URLs")
    return urls


def scrape_product_page(url: str) -> Product | None:
    """Scrape a single Monoprix product page using JSON-LD."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            log.debug(f"HTTP {resp.status_code} for {url}")
            return None
    except requests.RequestException as e:
        log.debug(f"Request failed for {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Extract JSON-LD structured data
    product_data = extract_json_ld(soup)
    if product_data:
        return product_data

    # Fallback: parse HTML directly
    return extract_from_html(soup, url)


def extract_json_ld(soup: BeautifulSoup) -> Product | None:
    """Extract product data from JSON-LD script tags."""
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single objects and arrays
        items = data if isinstance(data, list) else [data]

        for item in items:
            if item.get("@type") != "Product":
                continue

            # Extract offers/price
            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}

            price = 0.0
            try:
                price = float(offers.get("price", 0))
            except (ValueError, TypeError):
                pass

            # Brand
            brand_data = item.get("brand", {})
            brand = brand_data.get("name", "") if isinstance(brand_data, dict) else ""

            # Images
            images = item.get("image", [])
            image_url = ""
            if isinstance(images, list) and images:
                image_url = images[0]
            elif isinstance(images, str):
                image_url = images

            # URL
            product_url = item.get("url", "")

            # Category from breadcrumb (if available in same page)
            category = extract_category_from_url(product_url)

            return Product(
                name=item.get("name", ""),
                price=price,
                currency=offers.get("priceCurrency", "EUR"),
                brand=brand,
                image_url=image_url,
                product_url=product_url,
                sku=str(item.get("sku", "")),
                enseigne="Monoprix",
                category=category,
            )

    return None


def extract_from_html(soup: BeautifulSoup, url: str) -> Product | None:
    """Fallback: extract product data from HTML elements."""
    # Product name
    name_el = soup.select_one("h1.product-name") or soup.select_one(".pdp-title")
    name = name_el.get_text(strip=True) if name_el else ""
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True).split("|")[0].strip() if title else ""

    if not name:
        return None

    # Price
    price_el = soup.select_one(".price .sales .value") or soup.select_one(".classic-price .price")
    price = 0.0
    if price_el:
        price_text = price_el.get_text(strip=True)
        price = parse_price(price_text)
        if not price:
            # Try data attribute
            price_val = price_el.get("content") or price_el.get("data-price")
            if price_val:
                try:
                    price = float(price_val)
                except ValueError:
                    pass

    # Unit price
    unit_el = soup.select_one(".unit-price") or soup.select_one(".price-per-unit")
    unit_price = unit_el.get_text(strip=True) if unit_el else ""

    # Brand
    brand_el = soup.select_one(".product-flag-brand") or soup.select_one(".brand-name")
    brand = brand_el.get_text(strip=True) if brand_el else ""

    # Image
    img_el = soup.select_one(".primary-images img") or soup.select_one(".product-image img")
    image_url = ""
    if img_el:
        image_url = img_el.get("src") or img_el.get("data-src") or ""

    return Product(
        name=name,
        price=price,
        unit_price=unit_price,
        brand=brand,
        image_url=image_url,
        product_url=url,
        enseigne="Monoprix",
        category=extract_category_from_url(url),
    )


def extract_category_from_url(url: str) -> str:
    """Extract category from Monoprix URL pattern: /p/category/subcategory/..."""
    match = re.search(r"/p/([^/]+)/([^/]+)/", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return ""


def parse_price(text: str) -> float:
    """Parse French price: '4,99 EUR' -> 4.99"""
    cleaned = re.sub(r"[^\d,.]", "", text)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def run(max_products: int = 0, category_filter: str = ""):
    """Main scraping loop."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Get all product URLs from sitemap
    urls = fetch_sitemap_urls()
    if not urls:
        log.error("No product URLs found. Exiting.")
        return []

    # Filter by category if specified
    if category_filter:
        urls = [u for u in urls if category_filter.lower() in u.lower()]
        log.info(f"Filtered to {len(urls)} URLs matching '{category_filter}'")

    # Limit if specified
    if max_products > 0:
        urls = urls[:max_products]
        log.info(f"Limited to {max_products} products")

    # Step 2: Scrape each product page
    products = []
    for i, url in enumerate(urls):
        log.info(f"[{i+1}/{len(urls)}] Scraping: {url}")
        product = scrape_product_page(url)
        if product:
            products.append(product)
            log.info(f"  -> {product.name} | {product.price} EUR | {product.brand}")
        else:
            log.debug(f"  -> No data extracted")
        rate_limit()

    log.info(f"Total products scraped: {len(products)}")
    save_products(products, os.path.join(OUTPUT_DIR, "monoprix_products.json"))
    return products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Monoprix.fr")
    parser.add_argument("--max-products", type=int, default=0, help="Max products to scrape (0=all)")
    parser.add_argument("--category", type=str, default="", help="Filter by category keyword")
    args = parser.parse_args()

    run(max_products=args.max_products, category_filter=args.category)
