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

import json
import logging
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import BaseModel

from backend.chat import answer as chat_answer
from matching.embeddings import Embedder
from matching.index import ProductIndex
from matching.matcher import Matcher
from ner.extractor import OllamaExtractor
from ocr.paddle_ocr import ReceiptOCR


MAX_IMAGE_SIDE = 1600  # downscale large photos to limit RAM usage

log = logging.getLogger("smartfoyer.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# ─── App configuration ───────────────────────────────────────────────
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
INDEX_PREFIX = DATA_ROOT / "index" / "catalog"
RECEIPTS_DIR = DATA_ROOT / "receipts"
OCR_LANG = "fr"  # French receipts (Intermarche, Monoprix, Lidl, ...)
OLLAMA_MODEL = "llama3.1:8b"


# ─── Pipeline (lazy-loaded singletons) ───────────────────────────────
_ocr: ReceiptOCR | None = None
_extractor: OllamaExtractor | None = None
_matcher: Matcher | None = None


def get_ocr() -> ReceiptOCR:
    global _ocr
    if _ocr is None:
        log.info("Loading PaddleOCR...")
        _ocr = ReceiptOCR(lang=OCR_LANG)
    return _ocr


def get_extractor() -> OllamaExtractor:
    global _extractor
    if _extractor is None:
        log.info("Initializing Ollama extractor (%s)...", OLLAMA_MODEL)
        _extractor = OllamaExtractor(model=OLLAMA_MODEL)
    return _extractor


def get_matcher() -> Matcher | None:
    global _matcher
    if _matcher is None:
        index_file = INDEX_PREFIX.parent / (INDEX_PREFIX.name + ".faiss")
        if not index_file.exists():
            log.warning("FAISS index not found at %s - matching disabled.", index_file)
            return None
        log.info("Loading FAISS catalog index...")
        embedder = Embedder()
        idx = ProductIndex.load(str(INDEX_PREFIX), embedder)
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
        "total": matcher.index.index.ntotal,
        "by_enseigne": by_enseigne,
    }


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@app.post("/scan")
async def scan(image: UploadFile = File(...)):
    """Run the full pipeline on an uploaded image and return the result."""
    suffix = Path(image.filename or "").suffix.lower()
    looks_like_image = (
        (image.content_type or "").startswith("image/")
        or suffix in _IMAGE_EXTS
    )
    if not looks_like_image:
        raise HTTPException(400, detail="File must be an image")

    # Save upload to a temp file (PaddleOCR works on disk paths)
    suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name

    try:
        # Downscale large photos before OCR to keep RAM usage in check
        with Image.open(tmp_path) as im:
            w, h = im.size
            max_side = max(w, h)
            if max_side > MAX_IMAGE_SIDE:
                scale = MAX_IMAGE_SIDE / max_side
                im = im.convert("RGB").resize(
                    (int(w * scale), int(h * scale)), Image.LANCZOS
                )
                im.save(tmp_path, "JPEG", quality=88)
                log.info("Resized image from %dx%d to %dx%d", w, h, im.width, im.height)

        # 1. OCR
        log.info("Running OCR on %s", tmp_path)
        ocr_result = get_ocr().extract(tmp_path)

        # 2. NER
        log.info("Running NER on %d OCR lines", len(ocr_result.lines))
        receipt = get_extractor().extract(ocr_result.text)

        # 3. Matching (optional, only if FAISS index is available)
        matcher = get_matcher()
        comparisons: list[dict] = []
        total_savings = 0.0
        if matcher is not None and receipt.items:
            log.info("Running matching on %d items", len(receipt.items))
            results = matcher.compare(receipt)
            for r in results:
                comparisons.append(r.to_dict())
                total_savings += r.savings or 0.0

        response = {
            "id": "",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "ocr": {
                "text": ocr_result.text,
                "avg_confidence": ocr_result.avg_confidence,
                "line_count": len(ocr_result.lines),
            },
            "receipt": receipt.to_dict(),
            "comparisons": comparisons,
            "total_savings": round(total_savings, 2),
        }
        response["id"] = _save_receipt(response)
        return response
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


# ─── Receipt history ──────────────────────────────────────────────────


def _save_receipt(payload: dict) -> str:
    """Persist a /scan result as a JSON file and return its short id."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    receipt_id = uuid.uuid4().hex[:12]
    payload["id"] = receipt_id
    path = RECEIPTS_DIR / f"{receipt_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("Receipt saved: %s", path)
    return receipt_id


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
    return {
        "id": receipt.get("id", ""),
        "scanned_at": receipt.get("scanned_at", ""),
        "enseigne": r.get("enseigne", ""),
        "date": r.get("date", ""),
        "total": r.get("total", 0.0),
        "n_items": len(r.get("items") or []),
        "total_savings": receipt.get("total_savings", 0.0),
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
    }


@app.get("/history/{receipt_id}")
def history_detail(receipt_id: str):
    """Return the full stored payload of a past receipt."""
    path = RECEIPTS_DIR / f"{receipt_id}.json"
    if not path.exists():
        raise HTTPException(404, detail="Receipt not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
            model=OLLAMA_MODEL,
        )
    except Exception as e:
        log.exception("Chat failed")
        raise HTTPException(500, detail=f"Chat error: {e}")

    return {"answer": reply}
