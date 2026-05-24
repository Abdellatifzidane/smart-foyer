"""
SmartFoyer Backend API
======================
Exposes the full pipeline (OCR + NER + Matching) as HTTP endpoints
so the Flutter mobile/web app can scan receipts.

Endpoints:
  GET  /                  -> health check
  GET  /catalog/stats     -> number of products in the FAISS index, breakdown by enseigne
  POST /scan              -> upload a receipt image, returns parsed Receipt + comparisons
  GET  /history           -> list of past scanned receipts (summary)
  GET  /history/stats     -> aggregations (total, by enseigne, by month)
  GET  /history/{id}      -> full details of one past receipt

Run:
  uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

load_dotenv(override=True)

from backend.chat import answer as chat_answer
from matching.embeddings import Embedder
from matching.index import ProductIndex
from matching.matcher import Matcher
from ner.extractor import GroqExtractor
from ocr.paddle_ocr import ReceiptOCR


MAX_IMAGE_SIDE = 1600  # downscale large photos to limit RAM usage

log = logging.getLogger("smartfoyer.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# ─── App configuration ───────────────────────────────────────────────
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
INDEX_PREFIX = DATA_ROOT / "index" / "catalog"
RECEIPTS_DIR = DATA_ROOT / "receipts"
RECEIPT_IMAGES_DIR = RECEIPTS_DIR / "images"
MANUAL_PRODUCTS_PATH = DATA_ROOT / "manual_products.json"
OCR_LANG = "fr"  # French receipts (Intermarche, Monoprix, Lidl, ...)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


# ─── Pipeline (lazy-loaded singletons) ───────────────────────────────
_ocr: ReceiptOCR | None = None
_extractor: GroqExtractor | None = None
_matcher: Matcher | None = None
_embedder: Embedder | None = None


def get_ocr() -> ReceiptOCR:
    global _ocr
    if _ocr is None:
        log.info("Loading PaddleOCR...")
        _ocr = ReceiptOCR(lang=OCR_LANG)
    return _ocr


def get_extractor() -> GroqExtractor:
    global _extractor
    if _extractor is None:
        log.info("Initializing Groq extractor (%s)...", GROQ_MODEL)
        _extractor = GroqExtractor(model=GROQ_MODEL)
    return _extractor


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        log.info("Loading sentence-transformers embedder...")
        _embedder = Embedder()
    return _embedder


def get_matcher() -> Matcher | None:
    """Read-only matcher access. Returns None if no index exists on disk."""
    global _matcher
    if _matcher is None:
        index_file = INDEX_PREFIX.parent / (INDEX_PREFIX.name + ".faiss")
        if not index_file.exists():
            log.warning("FAISS index not found at %s - matching disabled.", index_file)
            return None
        log.info("Loading FAISS catalog index...")
        idx = ProductIndex.load(str(INDEX_PREFIX), _get_embedder())
        _matcher = Matcher(index=idx)
    return _matcher


def get_or_create_matcher() -> Matcher:
    """Used by admin endpoints. Creates an empty index on disk if none exists."""
    global _matcher
    if _matcher is None:
        index_file = INDEX_PREFIX.parent / (INDEX_PREFIX.name + ".faiss")
        embedder = _get_embedder()
        if index_file.exists():
            log.info("Loading FAISS catalog index...")
            idx = ProductIndex.load(str(INDEX_PREFIX), embedder)
        else:
            log.info("Creating empty FAISS index at %s", INDEX_PREFIX)
            idx = ProductIndex.empty(embedder, prefix=str(INDEX_PREFIX))
        _matcher = Matcher(index=idx)
    return _matcher


# ─── FastAPI app ─────────────────────────────────────────────────────
app = FastAPI(title="SmartFoyer API", version="0.1.0")

# CORS - allow Flutter web app to call this API from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global error handler ────────────────────────────────────────────
# Any unhandled exception becomes a structured JSON 500 with CORS headers,
# so the Flutter client can read the error message instead of getting an
# opaque network failure. The server stays up.


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "type": type(exc).__name__,
            "message": str(exc) or "Unexpected server error",
            "path": request.url.path,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/")
def root():
    return {"service": "SmartFoyer API", "status": "ok"}


@app.get("/catalog/stats")
def catalog_stats():
    matcher = get_matcher()
    if matcher is None:
        return {"loaded": False, "total": 0, "by_enseigne": {}}

    by_enseigne: dict[str, int] = {}
    for p in matcher.index.products:
        ens = p.get("enseigne", "?")
        by_enseigne[ens] = by_enseigne.get(ens, 0) + 1
    return {
        "loaded": True,
        "total": len(matcher.index.products),  # live count, ignoring tombstones
        "by_enseigne": by_enseigne,
    }


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@app.post("/scan")
async def scan(image: UploadFile = File(...)):
    """Run the full pipeline on an uploaded image and return the result.

    Robust by design: every stage (OCR, NER, matching) is wrapped so a failure
    in one stage degrades the response (partial result + error message)
    instead of crashing the server. The client always gets HTTP 200 with a
    `pipeline.errors` list describing what failed.
    """
    suffix = Path(image.filename or "").suffix.lower()
    looks_like_image = (
        (image.content_type or "").startswith("image/")
        or suffix in _IMAGE_EXTS
    )
    if not looks_like_image:
        raise HTTPException(400, detail="File must be an image")

    # Save upload to a temp file (PaddleOCR works on disk paths)
    suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await image.read())
            tmp_path = tmp.name
    except Exception as e:
        log.exception("Failed to persist uploaded image")
        raise HTTPException(500, detail=f"Cannot read upload: {e}")

    pipeline_errors: list[str] = []
    ocr_text = ""
    ocr_conf = 0.0
    ocr_lines_count = 0
    receipt_dict: dict = {"enseigne": "", "total": 0.0, "items": [], "date": ""}
    comparisons: list[dict] = []
    total_savings = 0.0

    try:
        # ─── 0. Preprocess image (resize) ─────────────────────────────
        try:
            with Image.open(tmp_path) as im:
                w, h = im.size
                max_side = max(w, h)
                if max_side > MAX_IMAGE_SIDE:
                    scale = MAX_IMAGE_SIDE / max_side
                    im = im.convert("RGB").resize(
                        (int(w * scale), int(h * scale)), Image.LANCZOS
                    )
                    im.save(tmp_path, "JPEG", quality=88)
                    log.info(
                        "Resized image from %dx%d to %dx%d",
                        w, h, im.width, im.height,
                    )
        except Exception as e:
            log.exception("Image preprocessing failed")
            pipeline_errors.append(f"preprocess: {e}")

        # ─── 1. OCR ───────────────────────────────────────────────────
        try:
            log.info("Running OCR on %s", tmp_path)
            ocr_result = get_ocr().extract(tmp_path)
            ocr_text = ocr_result.text
            ocr_conf = ocr_result.avg_confidence
            ocr_lines_count = len(ocr_result.lines)
        except Exception as e:
            log.exception("OCR failed")
            pipeline_errors.append(f"ocr: {e}")

        # ─── 2. NER ───────────────────────────────────────────────────
        if ocr_text:
            try:
                log.info("Running NER on %d OCR lines", ocr_lines_count)
                receipt = get_extractor().extract(ocr_text)
                receipt_dict = receipt.to_dict()
            except Exception as e:
                log.exception("NER failed")
                pipeline_errors.append(f"ner: {e}")
                receipt = None
        else:
            receipt = None

        # ─── 3. Matching (best-effort) ────────────────────────────────
        if receipt is not None and receipt.items:
            try:
                matcher = get_matcher()
                if matcher is not None:
                    log.info("Running matching on %d items", len(receipt.items))
                    for r in matcher.compare(receipt):
                        comparisons.append(r.to_dict())
                        total_savings += r.savings or 0.0
            except Exception as e:
                log.exception("Matching failed")
                pipeline_errors.append(f"matching: {e}")

        # ─── 4. Save (best-effort: never block the response) ──────────
        response = {
            "id": "",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "ocr": {
                "text": ocr_text,
                "avg_confidence": ocr_conf,
                "line_count": ocr_lines_count,
            },
            "receipt": receipt_dict,
            "comparisons": comparisons,
            "total_savings": round(total_savings, 2),
            "pipeline": {
                "ok": not pipeline_errors,
                "errors": pipeline_errors,
            },
        }
        try:
            receipt_id, image_ext = _save_receipt(response, image_path=tmp_path)
            response["id"] = receipt_id
            response["image_url"] = (
                f"/history/{receipt_id}/image" if image_ext else ""
            )
        except Exception as e:
            log.exception("Saving receipt failed")
            pipeline_errors.append(f"save: {e}")
            response["pipeline"]["errors"] = pipeline_errors
            response["pipeline"]["ok"] = False
            response["image_url"] = ""

        return response
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


# ─── Receipt history ──────────────────────────────────────────────────


def _save_receipt(payload: dict, image_path: str | None = None) -> tuple[str, str]:
    """Persist a /scan result and the original image.

    Returns (receipt_id, image_ext). image_ext is empty if no image was saved.
    """
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    receipt_id = uuid.uuid4().hex[:12]
    payload["id"] = receipt_id

    # Copy the (possibly downscaled) image alongside the JSON so the user can
    # later compare the original ticket against the extracted products.
    image_ext = ""
    if image_path:
        src = Path(image_path)
        if src.exists():
            ext = src.suffix.lower() or ".jpg"
            if ext not in _IMAGE_EXTS:
                ext = ".jpg"
            dst = RECEIPT_IMAGES_DIR / f"{receipt_id}{ext}"
            try:
                dst.write_bytes(src.read_bytes())
                image_ext = ext
                payload.setdefault("image_url", f"/history/{receipt_id}/image")
            except OSError:
                log.exception("Failed to save receipt image")

    path = RECEIPTS_DIR / f"{receipt_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("Receipt saved: %s", path)
    return receipt_id, image_ext


def _receipt_image_path(receipt_id: str) -> Path | None:
    """Locate the original image for a stored receipt (any supported ext)."""
    if not RECEIPT_IMAGES_DIR.exists():
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        p = RECEIPT_IMAGES_DIR / f"{receipt_id}{ext}"
        if p.exists():
            return p
    return None


def _load_all_receipts() -> list[dict]:
    """Load every persisted receipt, newest first."""
    if not RECEIPTS_DIR.exists():
        return []
    receipts = []
    for path in RECEIPTS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                receipts.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    receipts.sort(key=lambda r: r.get("scanned_at", ""), reverse=True)
    return receipts


def _summarize(receipt: dict) -> dict:
    """Compact summary used in history listings (without full OCR text)."""
    r = receipt.get("receipt") or {}
    rid = receipt.get("id", "")
    has_image = _receipt_image_path(rid) is not None if rid else False
    return {
        "id": rid,
        "scanned_at": receipt.get("scanned_at", ""),
        "enseigne": r.get("enseigne", ""),
        "date": r.get("date", ""),
        "total": r.get("total", 0.0),
        "n_items": len(r.get("items") or []),
        "total_savings": receipt.get("total_savings", 0.0),
        "image_url": f"/history/{rid}/image" if has_image else "",
    }


@app.get("/history")
def history():
    """Return the list of past receipts (summaries, newest first)."""
    return [_summarize(r) for r in _load_all_receipts()]


@app.get("/history/stats")
def history_stats():
    """Aggregate spending across all stored receipts."""
    receipts = _load_all_receipts()
    by_enseigne: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    total_spent = 0.0
    total_savings = 0.0

    for r in receipts:
        receipt_data = r.get("receipt") or {}
        total = float(receipt_data.get("total") or 0)
        total_spent += total
        total_savings += float(r.get("total_savings") or 0)

        ens = receipt_data.get("enseigne") or "Inconnu"
        by_enseigne[ens] += total

        month = (r.get("scanned_at") or "")[:7]  # YYYY-MM
        if month:
            by_month[month] += total

    return {
        "n_receipts": len(receipts),
        "total_spent": round(total_spent, 2),
        "total_savings": round(total_savings, 2),
        "by_enseigne": {k: round(v, 2) for k, v in by_enseigne.items()},
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "by_week": _build_weekly_stats(receipts),
        "by_category": _build_category_stats(receipts),
    }


@app.get("/history/{receipt_id}")
def history_detail(receipt_id: str):
    """Return the full stored payload of a past receipt."""
    path = RECEIPTS_DIR / f"{receipt_id}.json"
    if not path.exists():
        raise HTTPException(404, detail="Receipt not found")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    # Backfill image_url for receipts saved before this field was introduced
    if _receipt_image_path(receipt_id) is not None:
        payload["image_url"] = f"/history/{receipt_id}/image"
    return payload


@app.get("/history/{receipt_id}/image")
def history_image(receipt_id: str):
    """Stream the original ticket photo (so the user can compare it to the
    extracted products)."""
    img = _receipt_image_path(receipt_id)
    if img is None:
        raise HTTPException(404, detail="Image not found")
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(img.suffix.lower(), "application/octet-stream")
    return FileResponse(str(img), media_type=media_type)


def _build_weekly_stats(receipts: list[dict]) -> dict[str, float]:
    """Aggregate spending by ISO week (YYYY-Www) — used by the analytics view."""
    from datetime import datetime as _dt

    by_week: dict[str, float] = defaultdict(float)
    for r in receipts:
        receipt_data = r.get("receipt") or {}
        total = float(receipt_data.get("total") or 0)
        # Prefer the receipt's own date, fall back to scanned_at
        date_str = receipt_data.get("date") or r.get("scanned_at") or ""
        date_str = date_str[:10]
        try:
            d = _dt.fromisoformat(date_str)
        except ValueError:
            continue
        iso_year, iso_week, _ = d.isocalendar()
        by_week[f"{iso_year}-W{iso_week:02d}"] += total
    return {k: round(v, 2) for k, v in sorted(by_week.items())}


def _build_category_stats(receipts: list[dict]) -> dict[str, float]:
    """Lightweight spending breakdown by coarse category, inferred from the
    matched catalog category when available, otherwise from keywords in the
    product name."""
    KEYWORDS = {
        "Boulangerie": ("pain", "baguette", "viennois", "brioche", "croissant"),
        "Hygiene": ("desinfect", "savon", "dentifrice", "shampoing", "gel"),
        "Boissons": ("eau", "jus", "soda", "coca", "vin", "biere", "energy"),
        "Cremerie": ("lait", "yaourt", "fromage", "beurre", "creme"),
        "Surgele": ("surgele", "glace"),
        "Charcuterie": ("jambon", "saucisse", "lardon", "pate"),
        "Sucreries": ("chocolat", "bonbon", "biscuit", "galette", "gateau"),
        "Fruits/Legumes": ("pomme", "banane", "tomate", "salade", "carotte", "fruit", "legume"),
        "Non alimentaire": ("ecouteur", "pile", "ampoule", "briquet", "carafe"),
    }

    by_cat: dict[str, float] = defaultdict(float)
    for r in receipts:
        receipt_data = r.get("receipt") or {}
        for it in receipt_data.get("items") or []:
            price = float(it.get("price") or 0)
            if price <= 0:
                continue
            name = (it.get("name") or "").lower()
            matched = "Autres"
            for cat, kws in KEYWORDS.items():
                if any(kw in name for kw in kws):
                    matched = cat
                    break
            by_cat[matched] += price
    return {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])}


# ─── Conversational agent (RAG) ───────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


@app.post("/chat")
def chat(req: ChatRequest):
    """Answer a free-form question using the stored receipts as context."""
    if not req.question.strip():
        raise HTTPException(400, detail="Empty question")

    try:
        reply = chat_answer(
            question=req.question.strip(),
            receipts_dir=RECEIPTS_DIR,
            history=[m.model_dump() for m in req.history],
            model=GROQ_MODEL,
        )
    except Exception as e:
        log.exception("Chat failed")
        raise HTTPException(500, detail=f"Chat error: {e}")

    return {"answer": reply}


# ─── Admin: catalog CRUD ─────────────────────────────────────────────


class ProductIn(BaseModel):
    name: str
    price: float = 0.0
    currency: str = "EUR"
    unit_price: str = ""
    brand: str = ""
    image_url: str = ""
    product_url: str = ""
    enseigne: str = ""
    category: str = ""
    sku: str = ""


def _append_manual_product(product: dict, source: str = "admin") -> None:
    """Persist a manually-added product to data/manual_products.json so it
    survives a future `python -m matching.build_index` rebuild."""
    MANUAL_PRODUCTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if MANUAL_PRODUCTS_PATH.exists():
        try:
            with open(MANUAL_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []
    record = dict(product)
    record["_source"] = source
    existing.append(record)
    with open(MANUAL_PRODUCTS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


@app.get("/catalog/products")
def list_products(
    page: int = 1,
    page_size: int = 20,
    q: str = "",
    enseigne: str = "",
):
    """Paginated product listing with name substring + enseigne filters."""
    matcher = get_matcher()
    if matcher is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    products = matcher.index.products
    if q:
        ql = q.lower()
        products = [p for p in products if ql in (p.get("name", "").lower())]
    if enseigne:
        products = [p for p in products if p.get("enseigne", "") == enseigne]

    total = len(products)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return {
        "items": products[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/catalog/products")
def create_product(product: ProductIn):
    """Add a new product to the live FAISS index and persist it."""
    matcher = get_or_create_matcher()
    p_dict = product.model_dump()
    p_dict["scraped_at"] = datetime.now(timezone.utc).isoformat()
    try:
        pid = matcher.index.add_product(p_dict)
    except Exception as e:
        log.exception("add_product failed")
        raise HTTPException(500, detail=f"Failed to add product: {e}")
    _append_manual_product(p_dict, source="admin")
    return p_dict


@app.put("/catalog/products/{product_id}")
def update_product(product_id: str, product: ProductIn):
    """Update an existing product."""
    matcher = get_matcher()
    if matcher is None:
        raise HTTPException(404, detail="No catalog exists yet")
    try:
        updated = matcher.index.update_product(product_id, product.model_dump())
    except KeyError:
        raise HTTPException(404, detail="Product not found")
    except Exception as e:
        log.exception("update_product failed")
        raise HTTPException(500, detail=f"Failed to update product: {e}")
    return updated


@app.delete("/catalog/products/{product_id}")
def delete_product(product_id: str):
    """Remove a product (tombstoned in FAISS)."""
    matcher = get_matcher()
    if matcher is None:
        raise HTTPException(404, detail="No catalog exists yet")
    try:
        matcher.index.remove_product(product_id)
    except KeyError:
        raise HTTPException(404, detail="Product not found")
    return {"ok": True, "id": product_id}


# ─── Admin: scraper jobs ─────────────────────────────────────────────


class ScrapeRequest(BaseModel):
    retailer: str  # "lidl" or "monoprix"
    max_products: int = 100


# job_id -> {state, retailer, max_products, scraped, error, started_at, finished_at}
_jobs: dict[str, dict] = {}


def _run_scrape_job(job_id: str, retailer: str, max_products: int) -> None:
    """Sync worker — runs in a thread via asyncio.to_thread."""
    job = _jobs[job_id]

    def progress(n: int) -> None:
        job["scraped"] = n

    try:
        # Lazy import so the backend boots fast and doesn't pull network on import
        if retailer == "lidl":
            from scrapers.scraper_lidl import run as run_scraper
        elif retailer == "monoprix":
            from scrapers.scraper_monoprix import run as run_scraper
        else:
            raise ValueError(f"Unknown retailer: {retailer}")

        products = run_scraper(max_products=max_products, progress_cb=progress)

        # Push results into the live index
        matcher = get_or_create_matcher()
        for p in products or []:
            p_dict = p.to_dict() if hasattr(p, "to_dict") else dict(p)
            try:
                matcher.index.add_product(p_dict)
                _append_manual_product(p_dict, source=f"scraper-{retailer}")
            except Exception:
                log.exception("Failed to index scraped product")

        job["scraped"] = len(products or [])
        job["state"] = "done"
    except Exception as e:
        log.exception("Scrape job %s failed", job_id)
        job["state"] = "error"
        job["error"] = str(e)
    finally:
        job["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/admin/scrape")
async def start_scrape(req: ScrapeRequest):
    """Launch a scraper in the background and return a job id."""
    retailer = req.retailer.lower().strip()
    if retailer not in ("lidl", "monoprix"):
        raise HTTPException(400, detail="retailer must be 'lidl' or 'monoprix'")
    if req.max_products <= 0 or req.max_products > 5000:
        raise HTTPException(400, detail="max_products must be in 1..5000")

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "retailer": retailer,
        "max_products": req.max_products,
        "scraped": 0,
        "state": "running",
        "error": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    # Fire and forget — the task will keep updating _jobs[job_id]
    asyncio.create_task(asyncio.to_thread(_run_scrape_job, job_id, retailer, req.max_products))
    return _jobs[job_id]


@app.get("/admin/scrape/status")
def scrape_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Unknown job id")
    return job
