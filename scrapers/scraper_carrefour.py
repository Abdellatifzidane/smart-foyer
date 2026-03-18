"""
Scraper Carrefour.fr
====================
Carrefour utilise un rendu JavaScript cote client.
On utilise Playwright (navigateur headless) pour charger les pages
et extraire les donnees produits depuis le DOM rendu.

Strategie :
  1. Naviguer sur les pages categories (epicerie, boissons, etc.)
  2. Scroll pour charger les produits (lazy loading)
  3. Extraire nom, prix, prix unitaire, marque, image
  4. Pagination via le bouton "Voir plus"

Usage :
  python scraper_carrefour.py
  python scraper_carrefour.py --categories "epicerie-salee,boissons"
  python scraper_carrefour.py --max-pages 3
"""

import argparse
import json
import os
import re

from playwright.sync_api import sync_playwright, Page, TimeoutError as PwTimeout

from config import BROWSER_USER_AGENT, CRAWL_DELAY, OUTPUT_DIR, get_logger, rate_limit
from models import Product, save_products

log = get_logger("carrefour")

BASE_URL = "https://www.carrefour.fr"

# Categories principales alimentaires
DEFAULT_CATEGORIES = [
    "r/epicerie-salee",
    "r/epicerie-sucree",
    "r/boissons",
    "r/produits-laitiers-oeufs-fromages",
    "r/fruits-et-legumes",
    "r/viandes-et-poissons",
    "r/surgeles",
    "r/boulangerie-patisserie",
    "r/hygiene-et-beaute",
    "r/entretien-et-nettoyage",
]


def extract_products_from_page(page: Page) -> list[Product]:
    """Extract product data from the currently loaded Carrefour page."""
    products = []

    # Carrefour utilise des data attributes sur les cartes produits
    # Essayer plusieurs selecteurs connus
    selectors = [
        "[data-testid='product-card']",
        ".product-card-content",
        "li[data-testid='product']",
        ".ds-product-card",
    ]

    cards = []
    for sel in selectors:
        cards = page.query_selector_all(sel)
        if cards:
            log.info(f"Found {len(cards)} products with selector: {sel}")
            break

    if not cards:
        # Fallback: try to extract from JSON embedded in script tags
        products = extract_from_json_ld(page)
        if products:
            return products
        log.warning("No product cards found on page")
        return []

    for card in cards:
        try:
            product = parse_product_card(card)
            if product:
                products.append(product)
        except Exception as e:
            log.debug(f"Error parsing card: {e}")
            continue

    return products


def parse_product_card(card) -> Product | None:
    """Parse a single product card element."""
    # Product name
    name_el = (
        card.query_selector("[data-testid='product-card-title']")
        or card.query_selector(".product-card-content__title")
        or card.query_selector("h2")
        or card.query_selector("a[title]")
    )
    name = name_el.inner_text().strip() if name_el else ""
    if not name:
        return None

    # Price
    price_el = (
        card.query_selector("[data-testid='product-card-price']")
        or card.query_selector(".product-card-content__price")
        or card.query_selector(".price")
    )
    price_text = price_el.inner_text().strip() if price_el else "0"
    price = parse_price(price_text)

    # Unit price (prix au kg/L)
    unit_el = (
        card.query_selector("[data-testid='product-card-unit-price']")
        or card.query_selector(".product-card-content__unit-price")
        or card.query_selector(".unit-price")
    )
    unit_price = unit_el.inner_text().strip() if unit_el else ""

    # Brand
    brand_el = (
        card.query_selector("[data-testid='product-card-brand']")
        or card.query_selector(".product-card-content__brand")
    )
    brand = brand_el.inner_text().strip() if brand_el else ""

    # Image
    img_el = card.query_selector("img")
    image_url = ""
    if img_el:
        image_url = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

    # Product URL
    link_el = card.query_selector("a[href]")
    product_url = ""
    if link_el:
        href = link_el.get_attribute("href") or ""
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

    return Product(
        name=name,
        price=price,
        unit_price=unit_price,
        brand=brand,
        image_url=image_url,
        product_url=product_url,
        enseigne="Carrefour",
    )


def extract_from_json_ld(page: Page) -> list[Product]:
    """Fallback: extract product data from JSON-LD scripts."""
    products = []
    scripts = page.query_selector_all("script[type='application/ld+json']")
    for script in scripts:
        try:
            data = json.loads(script.inner_text())
            if isinstance(data, list):
                for item in data:
                    p = parse_json_ld_product(item)
                    if p:
                        products.append(p)
            elif isinstance(data, dict):
                p = parse_json_ld_product(data)
                if p:
                    products.append(p)
        except json.JSONDecodeError:
            continue
    return products


def parse_json_ld_product(data: dict) -> Product | None:
    """Parse a JSON-LD Product object."""
    if data.get("@type") != "Product":
        return None
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = float(offers.get("price", 0))
    brand_data = data.get("brand", {})
    brand = brand_data.get("name", "") if isinstance(brand_data, dict) else str(brand_data)
    images = data.get("image", [])
    image_url = images[0] if isinstance(images, list) and images else str(images) if images else ""

    return Product(
        name=data.get("name", ""),
        price=price,
        currency=offers.get("priceCurrency", "EUR"),
        brand=brand,
        image_url=image_url,
        sku=data.get("sku", ""),
        enseigne="Carrefour",
    )


def parse_price(text: str) -> float:
    """Parse French price format: '3,49 EUR' -> 3.49"""
    cleaned = re.sub(r"[^\d,.]", "", text)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def scroll_to_load_all(page: Page, max_scrolls: int = 10):
    """Scroll down to trigger lazy loading of products."""
    for i in range(max_scrolls):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(1000)
        # Check if "load more" button exists and click it
        load_more = page.query_selector(
            "button[data-testid='load-more']"
        ) or page.query_selector(".pagination__load-more")
        if load_more and load_more.is_visible():
            load_more.click()
            page.wait_for_timeout(2000)


def scrape_category(page: Page, category_path: str, max_pages: int = 5) -> list[Product]:
    """Scrape all products from a category."""
    url = f"{BASE_URL}/{category_path}"
    log.info(f"Scraping category: {url}")
    all_products = []

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except PwTimeout:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Accept cookies if banner appears
    try:
        cookie_btn = page.query_selector(
            "#onetrust-accept-btn-handler"
        ) or page.query_selector("[data-testid='accept-cookies']")
        if cookie_btn and cookie_btn.is_visible():
            cookie_btn.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    for page_num in range(max_pages):
        log.info(f"  Page {page_num + 1}/{max_pages}")
        scroll_to_load_all(page)
        products = extract_products_from_page(page)
        all_products.extend(products)
        log.info(f"  Extracted {len(products)} products (total: {len(all_products)})")

        # Try next page
        next_btn = page.query_selector(
            "a[data-testid='next-page']"
        ) or page.query_selector(".pagination__next")
        if next_btn and next_btn.is_visible():
            next_btn.click()
            page.wait_for_timeout(3000)
            rate_limit()
        else:
            break

    return all_products


def run(categories: list[str] | None = None, max_pages: int = 5):
    """Main scraping loop."""
    categories = categories or DEFAULT_CATEGORIES
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

        for cat in categories:
            products = scrape_category(page, cat, max_pages=max_pages)
            all_products.extend(products)
            rate_limit()

        browser.close()

    # Deduplicate by product URL
    seen = set()
    unique = []
    for p in all_products:
        key = p.product_url or p.name
        if key not in seen:
            seen.add(key)
            unique.append(p)

    log.info(f"Total unique products: {len(unique)}")
    save_products(unique, os.path.join(OUTPUT_DIR, "carrefour_products.json"))
    return unique


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Carrefour.fr")
    parser.add_argument("--categories", type=str, help="Comma-separated category paths")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per category")
    args = parser.parse_args()

    cats = args.categories.split(",") if args.categories else None
    run(categories=cats, max_pages=args.max_pages)
