"""
Scraper Lidl.fr
===============
Lidl utilise un rendu JavaScript avec lazy loading.
Le robots.txt bloque la recherche et la pagination par parametres,
mais autorise les pages produits statiques.

Strategie :
  1. Parser le sitemap pour trouver les URLs produits
  2. Utiliser Playwright pour charger chaque page (rendu JS)
  3. Extraire les donnees depuis le DOM ou JSON-LD
  4. Fallback : scraper les pages categories accessibles

Usage :
  python scraper_lidl.py
  python scraper_lidl.py --max-products 50
  python scraper_lidl.py --mode categories
"""

import argparse
import gzip
import json
import os
import re
import xml.etree.ElementTree as ET

import requests
from playwright.sync_api import sync_playwright, Page, TimeoutError as PwTimeout

from config import (
    BROWSER_USER_AGENT,
    CRAWL_DELAY,
    OUTPUT_DIR,
    USER_AGENT,
    REQUEST_TIMEOUT,
    get_logger,
    rate_limit,
)
from models import Product, save_products

log = get_logger("lidl")

BASE_URL = "https://www.lidl.fr"
SITEMAP_URL = "https://www.lidl.fr/static/sitemap.xml"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Categories accessibles sans parametres bloques
CATEGORY_URLS = [
    "/c/alimentation/s10013248",
    "/c/boissons/s10013260",
    "/c/produits-frais/s10013240",
    "/c/surgeles/s10013256",
    "/c/bebe-enfant/s10013288",
    "/c/hygiene-beaute/s10013272",
    "/c/entretien-maison/s10013280",
]


# ─── Sitemap Discovery ──────────────────────────────────────────

def fetch_sitemap_urls() -> list[str]:
    """Fetch product URLs from Lidl sitemap."""
    log.info(f"Fetching sitemap: {SITEMAP_URL}")

    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Failed to fetch sitemap: {e}")
        return []

    root = ET.fromstring(resp.content)
    product_urls = []

    # Check if this is a sitemap index
    sub_sitemaps = root.findall("sm:sitemap", NS)
    if sub_sitemaps:
        for sm in sub_sitemaps:
            loc = sm.find("sm:loc", NS)
            if loc is not None and "product" in loc.text.lower():
                urls = fetch_sub_sitemap(loc.text)
                product_urls.extend(urls)
    else:
        # Direct URL list
        for url_el in root.findall("sm:url", NS):
            loc = url_el.find("sm:loc", NS)
            if loc is not None and "/p/" in loc.text:
                product_urls.append(loc.text)

    log.info(f"Found {len(product_urls)} product URLs from sitemap")
    return product_urls


def fetch_sub_sitemap(url: str) -> list[str]:
    """Fetch URLs from a sub-sitemap (may be gzipped)."""
    log.info(f"Fetching sub-sitemap: {url}")
    rate_limit()

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Failed to fetch sub-sitemap: {e}")
        return []

    # Handle gzipped sitemaps
    content = resp.content
    if url.endswith(".gz"):
        try:
            content = gzip.decompress(content)
        except Exception as e:
            log.error(f"Failed to decompress: {e}")
            return []

    root = ET.fromstring(content)
    urls = []
    for url_el in root.findall("sm:url", NS):
        loc = url_el.find("sm:loc", NS)
        if loc is not None:
            urls.append(loc.text)

    return urls


# ─── Product Page Scraping (Playwright) ──────────────────────────

def scrape_product_page(page: Page, url: str) -> Product | None:
    """Scrape a single Lidl product page using Playwright."""
    try:
        page.goto(url, wait_until="networkidle", timeout=20000)
    except PwTimeout:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except PwTimeout:
            log.debug(f"Timeout loading {url}")
            return None

    # Try JSON-LD first
    product = extract_json_ld(page)
    if product:
        product.product_url = url
        return product

    # Fallback: parse DOM
    return extract_from_dom(page, url)


def extract_json_ld(page: Page) -> Product | None:
    """Extract product data from JSON-LD in the page."""
    scripts = page.query_selector_all("script[type='application/ld+json']")

    for script in scripts:
        try:
            data = json.loads(script.inner_text())
        except (json.JSONDecodeError, Exception):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") != "Product":
                continue

            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}

            price = 0.0
            try:
                price = float(offers.get("price", 0))
            except (ValueError, TypeError):
                pass

            brand_data = item.get("brand", {})
            brand = brand_data.get("name", "") if isinstance(brand_data, dict) else ""

            images = item.get("image", [])
            image_url = images[0] if isinstance(images, list) and images else str(images) if images else ""

            return Product(
                name=item.get("name", ""),
                price=price,
                currency=offers.get("priceCurrency", "EUR"),
                brand=brand,
                image_url=image_url,
                sku=str(item.get("sku", "")),
                enseigne="Lidl",
            )

    return None


def extract_from_dom(page: Page, url: str) -> Product | None:
    """Fallback: extract product data from DOM elements."""
    # Product name
    name_el = (
        page.query_selector("h1.keyfacts__title")
        or page.query_selector("h1[data-v-]")
        or page.query_selector("h1")
    )
    name = name_el.inner_text().strip() if name_el else ""
    if not name:
        return None

    # Price
    price = 0.0
    price_el = (
        page.query_selector(".m-price__price")
        or page.query_selector(".pricebox__price")
        or page.query_selector("[class*='price'] .price")
    )
    if price_el:
        price = parse_price(price_el.inner_text())

    # Unit price
    unit_el = (
        page.query_selector(".m-price__basic-quantity")
        or page.query_selector(".pricebox__basic-quantity")
    )
    unit_price = unit_el.inner_text().strip() if unit_el else ""

    # Brand
    brand_el = page.query_selector(".keyfacts__brand") or page.query_selector("[class*='brand']")
    brand = brand_el.inner_text().strip() if brand_el else ""

    # Image
    img_el = page.query_selector(".gallery__image img") or page.query_selector("picture img")
    image_url = ""
    if img_el:
        image_url = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

    return Product(
        name=name,
        price=price,
        unit_price=unit_price,
        brand=brand,
        image_url=image_url,
        product_url=url,
        enseigne="Lidl",
    )


# ─── Category Scraping ──────────────────────────────────────────

def scrape_category_page(page: Page, category_path: str) -> list[Product]:
    """Scrape products from a Lidl category page."""
    url = f"{BASE_URL}{category_path}"
    log.info(f"Scraping category: {url}")

    try:
        page.goto(url, wait_until="networkidle", timeout=25000)
    except PwTimeout:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except PwTimeout:
            log.warning(f"Timeout on category: {url}")
            return []

    # Accept cookies
    try:
        cookie_btn = page.query_selector("#onetrust-accept-btn-handler")
        if cookie_btn and cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # Scroll to load products
    for _ in range(5):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(1500)

    products = []

    # Try extracting product cards
    cards = (
        page.query_selector_all(".product-grid-box")
        or page.query_selector_all("[class*='product-item']")
        or page.query_selector_all("article[class*='product']")
    )

    for card in cards:
        try:
            name_el = card.query_selector("h3") or card.query_selector("[class*='title']")
            name = name_el.inner_text().strip() if name_el else ""
            if not name:
                continue

            price_el = card.query_selector("[class*='price']")
            price = parse_price(price_el.inner_text()) if price_el else 0.0

            unit_el = card.query_selector("[class*='quantity']") or card.query_selector("[class*='unit']")
            unit_price = unit_el.inner_text().strip() if unit_el else ""

            img_el = card.query_selector("img")
            image_url = ""
            if img_el:
                image_url = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

            link_el = card.query_selector("a[href]")
            product_url = ""
            if link_el:
                href = link_el.get_attribute("href") or ""
                product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            products.append(Product(
                name=name,
                price=price,
                unit_price=unit_price,
                image_url=image_url,
                product_url=product_url,
                enseigne="Lidl",
            ))
        except Exception as e:
            log.debug(f"Error parsing card: {e}")
            continue

    log.info(f"  Found {len(products)} products in category")
    return products


def parse_price(text: str) -> float:
    """Parse French price."""
    cleaned = re.sub(r"[^\d,.]", "", text)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ─── Main ────────────────────────────────────────────────────────

def run(mode: str = "sitemap", max_products: int = 0):
    """Main scraping loop."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_products = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=BROWSER_USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="fr-FR",
        )
        page = context.new_page()

        if mode == "sitemap":
            urls = fetch_sitemap_urls()
            if max_products > 0:
                urls = urls[:max_products]

            for i, url in enumerate(urls):
                log.info(f"[{i+1}/{len(urls)}] {url}")
                product = scrape_product_page(page, url)
                if product:
                    all_products.append(product)
                    log.info(f"  -> {product.name} | {product.price} EUR")
                rate_limit()

        elif mode == "categories":
            for cat in CATEGORY_URLS:
                products = scrape_category_page(page, cat)
                all_products.extend(products)
                rate_limit()

        browser.close()

    # Deduplicate
    seen = set()
    unique = []
    for p in all_products:
        key = p.product_url or p.name
        if key not in seen:
            seen.add(key)
            unique.append(p)

    log.info(f"Total unique products: {len(unique)}")
    save_products(unique, os.path.join(OUTPUT_DIR, "lidl_products.json"))
    return unique


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Lidl.fr")
    parser.add_argument("--mode", choices=["sitemap", "categories"], default="sitemap",
                        help="Scraping mode: sitemap (individual pages) or categories")
    parser.add_argument("--max-products", type=int, default=0, help="Max products (0=all)")
    args = parser.parse_args()

    run(mode=args.mode, max_products=args.max_products)
