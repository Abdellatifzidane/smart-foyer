"""
Stockage des tickets, strictement isolé par utilisateur
=======================================================
Remplace l'ancien stockage en vrac (data/receipts/*.json partagés). Désormais :

  - métadonnées + lignes produit en base (tables receipts / receipt_items),
  - image originale sous data/users/{user_id}/images/{receipt_id}.ext,
  - payload /scan complet conservé en JSON pour réafficher le détail.

Toute lecture passe par un user_id : un utilisateur ne voit JAMAIS les tickets
d'un autre.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.db import DATA_ROOT, Receipt, ReceiptItem, User
from matching.normalize import infer_category


USERS_DIR = DATA_ROOT / "users"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def _user_images_dir(user_id: str) -> Path:
    return USERS_DIR / user_id / "images"


def image_path(user_id: str, receipt_id: str) -> Path | None:
    base = _user_images_dir(user_id)
    if not base.exists():
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        p = base / f"{receipt_id}{ext}"
        if p.exists():
            return p
    return None


def save_receipt(
    db: Session, user: User, payload: dict, image_tmp_path: str | None = None
) -> tuple[str, str]:
    """Persiste un résultat /scan pour `user`. Renvoie (receipt_id, image_url)."""
    receipt_data = payload.get("receipt") or {}

    rec = Receipt(
        user_id=user.id,
        enseigne=(receipt_data.get("enseigne") or "").strip(),
        date=(receipt_data.get("date") or "").strip(),
        total=float(receipt_data.get("total") or 0),
        total_savings=float(payload.get("total_savings") or 0),
        ocr_confidence=float((payload.get("ocr") or {}).get("avg_confidence") or 0),
    )
    db.add(rec)
    db.flush()  # attribue rec.id

    # Image originale, rangée sous le dossier du user
    image_ext = ""
    if image_tmp_path:
        src = Path(image_tmp_path)
        if src.exists():
            ext = src.suffix.lower()
            if ext not in _IMAGE_EXTS:
                ext = ".jpg"
            dst_dir = _user_images_dir(user.id)
            dst_dir.mkdir(parents=True, exist_ok=True)
            try:
                (dst_dir / f"{rec.id}{ext}").write_bytes(src.read_bytes())
                image_ext = ext
            except OSError:
                image_ext = ""
    rec.image_ext = image_ext

    # Lignes produit (pour stats SQL par catégorie / fréquence)
    for it in receipt_data.get("items") or []:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        db.add(ReceiptItem(
            receipt_id=rec.id,
            user_id=user.id,
            name=name,
            price=float(it.get("price") or 0),
            quantity=float(it.get("quantity") or 1) or 1.0,
            category=infer_category(name),
        ))

    # Payload complet (avec l'id réel et l'URL image)
    payload["id"] = rec.id
    payload["image_url"] = f"/history/{rec.id}/image" if image_ext else ""
    rec.payload_json = json.dumps(payload, ensure_ascii=False)

    db.commit()
    return rec.id, payload["image_url"]


def _summarize(rec: Receipt) -> dict:
    return {
        "id": rec.id,
        "scanned_at": rec.scanned_at.isoformat() if rec.scanned_at else "",
        "enseigne": rec.enseigne or "",
        "date": rec.date or "",
        "total": rec.total or 0.0,
        "n_items": len(rec.items),
        "total_savings": rec.total_savings or 0.0,
        "image_url": f"/history/{rec.id}/image" if rec.image_ext else "",
    }


def delete_receipt(db: Session, user: User, receipt_id: str) -> bool:
    """Supprime un ticket du user (lignes + image incluses). False si introuvable
    ou s'il n'appartient pas au user (isolation garantie)."""
    rec = (
        db.query(Receipt)
        .filter(Receipt.user_id == user.id, Receipt.id == receipt_id)
        .first()
    )
    if rec is None:
        return False

    # Supprime l'image originale si présente
    img = image_path(user.id, receipt_id)
    if img is not None:
        try:
            img.unlink(missing_ok=True)
        except OSError:
            pass

    db.delete(rec)  # cascade -> receipt_items
    db.commit()
    return True


def list_summaries(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(Receipt)
        .filter(Receipt.user_id == user.id)
        .order_by(Receipt.scanned_at.desc())
        .all()
    )
    return [_summarize(r) for r in rows]


def get_detail(db: Session, user: User, receipt_id: str) -> dict | None:
    rec = (
        db.query(Receipt)
        .filter(Receipt.user_id == user.id, Receipt.id == receipt_id)
        .first()
    )
    if rec is None:
        return None
    payload = rec.payload()
    payload.setdefault("id", rec.id)
    if rec.image_ext:
        payload["image_url"] = f"/history/{rec.id}/image"
    return payload


def load_payloads(db: Session, user: User, limit: int | None = None) -> list[dict]:
    """Payloads complets du user (pour l'agent IA), plus récents d'abord."""
    q = (
        db.query(Receipt)
        .filter(Receipt.user_id == user.id)
        .order_by(Receipt.scanned_at.desc())
    )
    if limit:
        q = q.limit(limit)
    out = []
    for rec in q.all():
        p = rec.payload()
        if not p:
            # Reconstruit un minimum si payload absent
            p = {"receipt": {"enseigne": rec.enseigne, "total": rec.total,
                             "date": rec.date, "items": []},
                 "total_savings": rec.total_savings}
        p["scanned_at"] = rec.scanned_at.isoformat() if rec.scanned_at else ""
        out.append(p)
    return out


def history_stats(db: Session, user: User) -> dict:
    """Agrégats de dépenses du user (SQL + payloads)."""
    receipts = (
        db.query(Receipt)
        .filter(Receipt.user_id == user.id)
        .order_by(Receipt.scanned_at.asc())
        .all()
    )
    by_enseigne: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    by_week: dict[str, float] = defaultdict(float)
    total_spent = 0.0
    total_savings = 0.0

    for r in receipts:
        total = float(r.total or 0)
        total_spent += total
        total_savings += float(r.total_savings or 0)
        by_enseigne[r.enseigne or "Inconnu"] += total

        scanned = r.scanned_at.isoformat() if r.scanned_at else ""
        month = scanned[:7]
        if month:
            by_month[month] += total
        date_str = (r.date or scanned)[:10]
        try:
            d = datetime.fromisoformat(date_str)
            iso_year, iso_week, _ = d.isocalendar()
            by_week[f"{iso_year}-W{iso_week:02d}"] += total
        except ValueError:
            pass

    # Catégories : agrégat SQL sur receipt_items
    by_category: dict[str, float] = defaultdict(float)
    items = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.user_id == user.id, ReceiptItem.price > 0)
        .all()
    )
    for it in items:
        by_category[it.category or "Autres"] += float(it.price or 0)

    return {
        "n_receipts": len(receipts),
        "total_spent": round(total_spent, 2),
        "total_savings": round(total_savings, 2),
        "by_enseigne": {k: round(v, 2) for k, v in by_enseigne.items()},
        "by_month": {k: round(v, 2) for k, v in sorted(by_month.items())},
        "by_week": {k: round(v, 2) for k, v in sorted(by_week.items())},
        "by_category": {k: round(v, 2)
                        for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])},
    }
