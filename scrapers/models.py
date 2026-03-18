"""Data models shared across all scrapers."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json


@dataclass
class Product:
    name: str
    price: float
    currency: str = "EUR"
    unit_price: str = ""          # e.g. "2.50 EUR/kg"
    brand: str = ""
    image_url: str = ""
    product_url: str = ""
    enseigne: str = ""
    category: str = ""
    sku: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


def save_products(products: list[Product], filepath: str):
    """Save a list of products to a JSON file."""
    data = [p.to_dict() for p in products]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data)} products to {filepath}")
