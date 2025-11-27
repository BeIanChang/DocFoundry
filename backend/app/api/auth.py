import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import jwt
from fastapi import APIRouter, HTTPException, Header

router = APIRouter(prefix="/auth", tags=["auth (dev JWT)"])

# in-memory user store for dev only (email -> {id, email, name, password_hash})
_users: Dict[str, Dict] = {}

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", "60"))


def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def _issue_token(user: Dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "exp": now + timedelta(minutes=JWT_EXP_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")


@router.post("/register")
def register(payload: Dict):
    """
    Dev-only registration issuing a JWT.
    body: {"email": "...", "password": "...", "name": "..."}
    """
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    name = payload.get("name") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")
    if email in _users:
        raise HTTPException(status_code=400, detail="user already exists")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "password_hash": _hash_password(password),
    }
    _users[email] = user
    token = _issue_token(user)
    return {"token": token, "user": {"id": user["id"], "email": email, "name": name}}


@router.post("/login")
def login(payload: Dict):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    user = _users.get(email)
    if not user or user["password_hash"] != _hash_password(password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = _issue_token(user)
    return {"token": token, "user": {"id": user["id"], "email": email, "name": user["name"]}}


def get_current_user(authorization: Optional[str] = Header(default=None)):
    """
    Dev-only bearer token checker. Expects: Authorization: Bearer <token>
    JWT carries user id/email; we return a dict with those claims.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid authorization format")
    token = parts[1]
    claims = _decode_token(token)
    # prefer stored user if present; otherwise use claims
    user = _users.get(claims.get("email")) or {
        "id": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name"),
    }
    return user
