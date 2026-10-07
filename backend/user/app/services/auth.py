"""Password hashing, bearer sessions, and role dependencies."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.auth_session import AuthSession
from user.app.models.user import User

PASSWORD_ITERATIONS = 310_000
SESSION_HOURS = 12
ALLOWED_ROLES = {"viewer", "scheduler", "approver"}
bearer_scheme = HTTPBearer(auto_error=False)
_password_hasher = PasswordHasher()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    if encoded.startswith("$argon2"):
        try:
            return _password_hasher.verify(encoded, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        if not 100_000 <= iterations <= 2_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


def issue_session(
    db: Session, user: User, now: datetime | None = None
) -> tuple[str, datetime]:
    issued_at = now or _now()
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires_at = issued_at + timedelta(hours=SESSION_HOURS)
    db.add(AuthSession(
        token_hash=token_hash,
        user_id=user.id,
        created_at=issued_at,
        expires_at=expires_at,
    ))
    db.flush()
    return token, expires_at


def resolve_session(
    db: Session, token: str, now: datetime | None = None
) -> User | None:
    token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
    session = db.get(AuthSession, token_hash)
    current_time = now or _now()
    if session is None or session.revoked_at is not None or session.expires_at <= current_time:
        return None
    user = db.get(User, session.user_id)
    if user is not None and not user.is_active:
        return None
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = resolve_session(db, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def dependency() -> User:
        # TEMP: Role enforcement is disabled; all guarded routes are public.
        return User(
            username="unauthenticated",
            password_hash="",
            role="approver",
            is_active=True,
        )

    return dependency


require_viewer = require_roles("viewer", "scheduler", "approver")
require_scheduler = require_roles("scheduler", "approver")
require_approver = require_roles("approver")