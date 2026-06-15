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

# Le modèle d'embedding (e5) est déjà téléchargé en cache après le premier
# `build_index`. On force le mode hors-ligne de Hugging Face AU RUNTIME pour que
# le backend charge le modèle depuis le cache sans jamais toucher le réseau
# (immunise contre un proxy d'entreprise injoignable / coupure réseau).
# Surcharge possible : HF_HUB_OFFLINE=0 pour réautoriser le réseau.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.orm import Session

load_dotenv(override=True)

from backend.auth import decode_token, get_current_user
from backend.auth import router as auth_router
from backend.chat import answer as chat_answer
from backend.db import User, db_dependency, init_db
from backend import receipts_store
from matching.embeddings import Embedder
from matching.index import ProductIndex
from matching.matcher import Matcher
from ner.extractor import GroqExtractor
# NB : ocr.paddle_ocr (PaddleOCR) est importé PARESSEUSEMENT dans get_ocr() pour
# que le backend démarre sans la lourde dépendance Paddle (auth/historique OK).


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


def get_ocr():
    global _ocr
    if _ocr is None:
        log.info("Loading PaddleOCR...")
        from ocr.paddle_ocr import ReceiptOCR  # import paresseux (dépendance lourde)
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
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()  # crée la base SQLite + les tables
    log.info("Database initialized.")
    yield


app = FastAPI(title="SmartFoyer API", version="0.2.0", lifespan=_lifespan)

# CORS - allow Flutter web app to call this API from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth (Google OAuth + email/mot de passe + JWT)
app.include_router(auth_router)


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
async def scan(
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
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
            receipt_id, image_url = receipts_store.save_receipt(
                db, user, response, image_tmp_path=tmp_path
            )
            response["id"] = receipt_id
            response["image_url"] = image_url
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


# ─── Receipt history (scoped per user) ────────────────────────────────


@app.get("/history")
def history(
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
    """Tickets de l'utilisateur courant (résumés, plus récents d'abord)."""
    return receipts_store.list_summaries(db, user)


@app.get("/history/stats")
def history_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
    """Agrégats de dépenses de l'utilisateur courant."""
    return receipts_store.history_stats(db, user)


@app.get("/history/{receipt_id}")
def history_detail(
    receipt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
    """Détail complet d'un ticket — 404 s'il n'appartient pas au user."""
    payload = receipts_store.get_detail(db, user, receipt_id)
    if payload is None:
        raise HTTPException(404, detail="Receipt not found")
    return payload


def _user_from_header_or_token(
    authorization: str | None, token: str | None, db: Session
) -> User:
    """Résout l'utilisateur depuis l'en-tête Bearer OU le query param `token`."""
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    elif token:
        raw = token.strip()
    if not raw:
        raise HTTPException(401, detail="Authentification requise")
    payload = decode_token(raw)
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(401, detail="Utilisateur introuvable")
    return user


@app.delete("/history/{receipt_id}")
def delete_history(
    receipt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
    """Supprime un ticket du user (404 s'il n'existe pas / n'est pas à lui)."""
    if not receipts_store.delete_receipt(db, user, receipt_id):
        raise HTTPException(404, detail="Receipt not found")
    return {"ok": True, "id": receipt_id}


@app.get("/history/{receipt_id}/image")
def history_image(
    receipt_id: str,
    token: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_dependency),
):
    """Photo originale du ticket (uniquement si elle appartient au user).

    Les balises <img> ne peuvent pas porter d'en-tête Authorization : on
    accepte donc aussi le JWT via le paramètre de requête `?token=...`.
    """
    user = _user_from_header_or_token(authorization, token, db)
    # On vérifie d'abord la propriété en base, puis on sert le fichier.
    if receipts_store.get_detail(db, user, receipt_id) is None:
        raise HTTPException(404, detail="Image not found")
    img = receipts_store.image_path(user.id, receipt_id)
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


# ─── Conversational agent (RAG) ───────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


@app.post("/chat")
def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dependency),
):
    """Réponse RAG fondée UNIQUEMENT sur les tickets de l'utilisateur courant."""
    if not req.question.strip():
        raise HTTPException(400, detail="Empty question")

    try:
        receipts = receipts_store.load_payloads(db, user)
        reply = chat_answer(
            question=req.question.strip(),
            receipts=receipts,
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
def create_product(product: ProductIn, user: User = Depends(get_current_user)):
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
def update_product(product_id: str, product: ProductIn, user: User = Depends(get_current_user)):
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
def delete_product(product_id: str, user: User = Depends(get_current_user)):
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
async def start_scrape(req: ScrapeRequest, user: User = Depends(get_current_user)):
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
