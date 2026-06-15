"""
Authentification : Google OAuth + email/mot de passe + JWT
==========================================================
Deux façons de se connecter, un seul type de session (JWT applicatif) :

  - **Google Sign-In** : le front obtient un *ID token* Google (via le Client ID
    Web), on le vérifie côté serveur contre les certificats Google, puis on
    crée/retrouve l'utilisateur et on émet notre JWT.
  - **Email + mot de passe** : filet de sécurité pour la démo (hash bcrypt).

Toutes les routes de données utilisent `get_current_user` : impossible de lire
les tickets d'un autre compte.

Variables d'environnement :
  GOOGLE_CLIENT_ID   (vide => Google désactivé, email/mdp reste dispo)
  JWT_SECRET, JWT_ALG, JWT_EXPIRE_MINUTES
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.db import User, db_dependency


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "10080"))  # 7 j


# ─── Mots de passe (bcrypt direct, robuste avec bcrypt 5.x) ──────────
def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]  # bcrypt limite à 72 octets
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─── JWT ─────────────────────────────────────────────────────────────
def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise HTTPException(401, detail=f"Token invalide : {e}")


# ─── Vérification de l'ID token Google ───────────────────────────────
def verify_google_token(id_token_str: str) -> dict:
    """Vérifie un ID token Google. Renvoie {sub, email, name, picture} ou 401."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, detail="Connexion Google non configurée sur le serveur")
    # Import paresseux : évite de charger google.auth si Google est inutilisé.
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token as g_id_token

    try:
        info = g_id_token.verify_oauth2_token(
            id_token_str, g_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        raise HTTPException(401, detail=f"ID token Google invalide : {e}")

    if not info.get("email"):
        raise HTTPException(401, detail="ID token Google sans email")
    if info.get("email_verified") is False:
        raise HTTPException(401, detail="Email Google non vérifié")
    return info


def verify_google_access_token(access_token: str) -> dict:
    """Vérifie un *access token* Google (cas Flutter Web : `signIn()` ne renvoie
    pas d'ID token mais un access token). On valide l'audience via tokeninfo
    puis on récupère le profil via userinfo. Renvoie {sub, email, name, picture}.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, detail="Connexion Google non configurée sur le serveur")
    import requests  # dépendance déjà présente

    # 1) Validation : le token a-t-il été émis pour NOTRE client ?
    try:
        ti = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token}, timeout=10,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"Google injoignable (tokeninfo) : {e}")
    if ti.status_code != 200:
        raise HTTPException(401, detail="Access token Google invalide")
    ti_data = ti.json()
    audience = ti_data.get("aud") or ti_data.get("azp")
    if audience != GOOGLE_CLIENT_ID:
        raise HTTPException(401, detail="Access token émis pour un autre client")

    # 2) Profil utilisateur
    try:
        ui = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=10,
        )
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"Google injoignable (userinfo) : {e}")
    if ui.status_code != 200:
        raise HTTPException(401, detail="Impossible de récupérer le profil Google")
    info = ui.json()
    # tokeninfo porte parfois l'email même si userinfo ne l'a pas (scopes)
    info.setdefault("email", ti_data.get("email", ""))
    info.setdefault("sub", ti_data.get("sub", ""))
    if not info.get("email"):
        raise HTTPException(401, detail="Compte Google sans email")
    return info


# ─── Dépendance : utilisateur courant ────────────────────────────────
def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_dependency),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="Authentification requise (Bearer token manquant)")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, detail="Utilisateur introuvable")
    return user


# ─── Schémas d'entrée/sortie ─────────────────────────────────────────
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleIn(BaseModel):
    # Flutter Web fournit un access_token ; les apps natives un id_token.
    id_token: str = ""
    access_token: str = ""


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ─── Routes ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut)
def register(body: RegisterIn, db: Session = Depends(db_dependency)):
    email = body.email.lower().strip()
    if len(body.password) < 6:
        raise HTTPException(400, detail="Mot de passe trop court (6 caractères minimum)")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, detail="Un compte existe déjà avec cet email")
    user = User(
        email=email,
        name=body.name.strip() or email.split("@")[0],
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    return AuthOut(access_token=create_access_token(user), user=user.to_public())


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(db_dependency)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(401, detail="Email ou mot de passe incorrect")
    return AuthOut(access_token=create_access_token(user), user=user.to_public())


@router.post("/google", response_model=AuthOut)
def google_login(body: GoogleIn, db: Session = Depends(db_dependency)):
    if body.id_token:
        info = verify_google_token(body.id_token)
    elif body.access_token:
        info = verify_google_access_token(body.access_token)
    else:
        raise HTTPException(400, detail="id_token ou access_token requis")
    sub = info.get("sub") or info.get("email")
    email = info["email"].lower().strip()

    # 1) compte Google déjà lié ? 2) sinon, email déjà utilisé ? on lie.
    user = db.query(User).filter(User.google_sub == sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email)
            db.add(user)
        user.google_sub = sub
    # Rafraîchit le profil depuis Google
    user.name = info.get("name", "") or user.name or email.split("@")[0]
    user.picture = info.get("picture", "") or user.picture
    db.commit()
    return AuthOut(access_token=create_access_token(user), user=user.to_public())


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user.to_public()
