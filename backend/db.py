"""
Couche de persistance SQLite / SQLAlchemy
=========================================
Repense la structure de données du POC : tout est désormais **rattaché à un
utilisateur**. Trois tables :

  - **users**         : comptes (Google et/ou email+mot de passe).
  - **receipts**      : un ticket scanné, appartenant à UN user (user_id).
  - **receipt_items** : les lignes produit d'un ticket (pour des stats SQL
                        propres : par catégorie, produits les plus achetés…).

Le payload complet du scan (OCR brut + comparaisons de prix) est conservé en
JSON dans `receipts.payload_json` pour réafficher le détail sans recalcul, mais
les champs servant aux agrégats sont aussi des colonnes indexables.

La base vit dans data/smartfoyer.db. Le catalogue produits (FAISS) reste
partagé entre tous les utilisateurs — ce sont des prix publics d'enseignes.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session


DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
# Surchargable pour les tests (base éphémère).
DB_URL = os.environ.get("SMARTFOYER_DB_URL", f"sqlite:///{DATA_ROOT / 'smartfoyer.db'}")

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


# ─── Modèles ─────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, default="")
    # Nul si compte Google-only ; sinon hash bcrypt.
    password_hash = Column(String, nullable=True)
    # Identifiant stable Google (claim "sub"), nul si compte email-only.
    google_sub = Column(String, unique=True, index=True, nullable=True)
    picture = Column(String, default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    receipts = relationship("Receipt", back_populates="user",
                            cascade="all, delete-orphan")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name or "",
            "picture": self.picture or "",
            "auth": "google" if self.google_sub else "password",
        }


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                     index=True, nullable=False)
    scanned_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
    enseigne = Column(String, default="", index=True)
    date = Column(String, default="")              # date imprimée sur le ticket
    total = Column(Float, default=0.0)
    total_savings = Column(Float, default=0.0)
    ocr_confidence = Column(Float, default=0.0)
    image_ext = Column(String, default="")          # "" si pas d'image
    payload_json = Column(Text, default="")          # payload /scan complet

    user = relationship("User", back_populates="receipts")
    items = relationship("ReceiptItem", back_populates="receipt",
                         cascade="all, delete-orphan")

    def payload(self) -> dict:
        try:
            return json.loads(self.payload_json) if self.payload_json else {}
        except json.JSONDecodeError:
            return {}


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String, ForeignKey("receipts.id", ondelete="CASCADE"),
                        index=True, nullable=False)
    # Dénormalisé pour pouvoir filtrer par user sans jointure.
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, default="")
    price = Column(Float, default=0.0)
    quantity = Column(Float, default=1.0)
    category = Column(String, default="", index=True)

    receipt = relationship("Receipt", back_populates="items")


class Feedback(Base):
    """Évaluation 👍/👎 d'un composant par l'utilisateur (OCR, matching, agent)."""
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                     index=True, nullable=False)
    # Composant évalué : "ocr" | "matching" | "agent".
    target = Column(String, index=True, nullable=False)
    # Note : "up" (👍) | "down" (👎).
    rating = Column(String, nullable=False)
    # Références facultatives selon la cible :
    receipt_id = Column(String, default="")   # pour ocr / matching
    question = Column(Text, default="")        # pour agent
    answer = Column(Text, default="")          # pour agent
    comment = Column(Text, default="")         # commentaire libre (surtout sur 👎)
    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)


# ─── Engine / sessions ───────────────────────────────────────────────
_engine = None
_SessionLocal = None


def _make_engine():
    connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
    if DB_URL.startswith("sqlite") and "memory" not in DB_URL:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return create_engine(DB_URL, connect_args=connect_args, future=True)


def init_db() -> None:
    """Crée l'engine, les tables, et la fabrique de sessions (idempotent)."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _make_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False,
                                     expire_on_commit=False, class_=Session)
        Base.metadata.create_all(_engine)


def get_session() -> Session:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


@contextmanager
def session_scope():
    """Session transactionnelle (commit/rollback automatiques)."""
    s = get_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# Dépendance FastAPI
def db_dependency():
    s = get_session()
    try:
        yield s
    finally:
        s.close()
